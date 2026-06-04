"""Streamlit 双栏仪表板：左侧对话，右侧图表、SQL 与决策洞察。"""
from __future__ import annotations

import html
import sys
import uuid
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.graph import build_graph
from config.settings import OUTPUT_CHARTS_DIR, RAW_DATA_DIR, check_raw_data_files


@st.cache_resource(show_spinner=False)
def get_compiled_graph():
    return build_graph()
EXAMPLE_QUESTIONS = [
    "2017年各州销售额排名怎样？",
    "平台整体准时交付率是多少？哪些州延迟最严重？",
    "哪种支付方式最受欢迎？平均分期数是多少？",
    "根据历史订单趋势，预测未来6周销售额并给出建议。",
]


def normalize_chart_paths(paths: list[str] | None) -> list[str]:
    """将图表路径解析为存在的绝对路径，避免 st.image 因相对路径失效。"""
    if not paths:
        return []
    seen: set[str] = set()
    resolved_list: list[str] = []
    for raw in paths:
        if not raw or not str(raw).strip():
            continue
        p = Path(str(raw).strip())
        candidates = [p, ROOT / p, OUTPUT_CHARTS_DIR / p.name]
        if p.is_absolute():
            candidates = [p, OUTPUT_CHARTS_DIR / p.name]
        for cand in candidates:
            try:
                resolved = cand.resolve()
            except OSError:
                continue
            key = str(resolved)
            if key in seen:
                break
            if resolved.is_file() and resolved.stat().st_size > 0:
                seen.add(key)
                resolved_list.append(key)
                break
    return resolved_list


def inject_sidebar_toggle_scripts() -> None:
    """展开：原生 >> 对齐品牌行；收起：窄条展开钮。每次 rerun 触发 sync，观察器只绑定一次。"""
    components.html(
        """
        <script>
        (function () {
            const win = window.parent;
            const doc = win.document;
            if (!win.__agenticSidebarToggle) {
                win.__agenticSidebarToggle = {};
            }
            const api = win.__agenticSidebarToggle;
            const RAIL_PX = 44;
            const PIN_PROPS = ["position", "top", "left", "width", "height", "z-index", "display"];

            function expandShell() {
                return doc.querySelector('[data-testid="collapsedControl"]')
                    || doc.querySelector('[data-testid="stSidebarCollapsedControl"]');
            }
            function sidebarCollapsed(sidebar) {
                if (!sidebar) return true;
                const attr = sidebar.getAttribute("aria-expanded");
                if (attr === "false") return true;
                if (attr === "true") return false;
                const w = sidebar.getBoundingClientRect().width;
                if (w > 0 && w < 120) return true;
                const content = sidebar.querySelector('[data-testid="stSidebarContent"]');
                if (content) {
                    const cs = win.getComputedStyle(content);
                    if (cs.display === "none" || cs.visibility === "hidden") return true;
                    if (cs.display !== "none" && w >= 160) return false;
                }
                const shell = expandShell();
                if (shell) {
                    const cs = win.getComputedStyle(shell);
                    if (cs.display !== "none" && cs.visibility !== "hidden" && cs.opacity !== "0") {
                        return true;
                    }
                }
                return false;
            }
            function isExpanded() {
                const sidebar = doc.querySelector('section[data-testid="stSidebar"]');
                if (!sidebar) return false;
                return !sidebarCollapsed(sidebar);
            }
            function nativeCollapseBtn() {
                return doc.querySelector('[data-testid="stSidebarCollapseButton"] button')
                    || doc.querySelector('[data-testid="stSidebarCollapseButton"]');
            }
            function nativeExpandBtn() {
                const shell = expandShell();
                if (shell) {
                    const btn = shell.querySelector("button");
                    if (btn) return btn;
                }
                return doc.querySelector('button[data-testid="stExpandSidebarButton"]')
                    || doc.querySelector('[data-testid="stExpandSidebarButton"]');
            }
            function showExpandControlShell() {
                const shell = expandShell();
                if (!shell) return;
                shell.style.setProperty("display", "flex", "important");
                shell.style.setProperty("visibility", "visible", "important");
                shell.style.setProperty("opacity", "1", "important");
                shell.style.setProperty("pointer-events", "auto", "important");
            }
            function clickNativeExpand() {
                const shell = expandShell();
                if (shell) {
                    const btn = shell.querySelector("button");
                    if (btn) { btn.click(); return; }
                    shell.click();
                    return;
                }
                const extra = [
                    'button[data-testid="stExpandSidebarButton"]',
                    '[data-testid="stExpandSidebarButton"]',
                    'header[data-testid="stHeader"] button[kind="header"]',
                ];
                for (const sel of extra) {
                    const el = doc.querySelector(sel);
                    if (el) { el.click(); return; }
                }
                nativeExpandBtn()?.click();
            }
            function clickNativeCollapse() {
                nativeCollapseBtn()?.click();
            }
            function clickToggle(ev) {
                if (ev) {
                    ev.preventDefault();
                    ev.stopPropagation();
                }
                if (isExpanded()) clickNativeCollapse();
                else clickNativeExpand();
            }

            let fallback = doc.getElementById("agentic-sidebar-toggle-btn");
            if (!fallback) {
                fallback = doc.createElement("button");
                fallback.id = "agentic-sidebar-toggle-btn";
                fallback.type = "button";
                fallback.className = "agentic-sidebar-toggle-fallback";
                fallback.title = "展开侧边栏";
                fallback.textContent = "\\u203A";
                doc.body.appendChild(fallback);
            }
            fallback.onclick = clickToggle;

            function unpinButton(btn) {
                if (!btn) return;
                PIN_PROPS.forEach((p) => btn.style.removeProperty(p));
            }

            function pinButton(btn, top, left, size) {
                if (!btn) return;
                btn.style.setProperty("position", "fixed", "important");
                btn.style.setProperty("top", top + "px", "important");
                btn.style.setProperty("left", left + "px", "important");
                btn.style.setProperty("width", size + "px", "important");
                btn.style.setProperty("height", size + "px", "important");
                btn.style.setProperty("display", "inline-flex", "important");
                btn.style.setProperty("align-items", "center", "important");
                btn.style.setProperty("justify-content", "center", "important");
                btn.style.setProperty("z-index", "999999", "important");
                btn.style.setProperty("visibility", "visible", "important");
                btn.style.setProperty("opacity", "1", "important");
                btn.style.setProperty("pointer-events", "auto", "important");
                btn.style.setProperty("background", "transparent", "important");
                btn.style.setProperty("border", "none", "important");
                btn.style.setProperty("box-shadow", "none", "important");
                btn.style.setProperty("outline", "none", "important");
            }

            function isInSidebarContent(node) {
                return Boolean(node && node.closest('[data-testid="stSidebarContent"]'));
            }

            function hideNativeToggle(btn) {
                if (!btn || isInSidebarContent(btn)) return;
                unpinButton(btn);
                const wrap = btn.closest(
                    '[data-testid="stSidebarCollapseButton"], [data-testid="collapsedControl"], [data-testid="stSidebarCollapsedControl"]'
                );
                if (wrap && isInSidebarContent(wrap)) return;
                [btn, wrap].filter(Boolean).forEach((node) => {
                    node.style.setProperty("display", "none", "important");
                    node.style.setProperty("visibility", "hidden", "important");
                    node.style.setProperty("opacity", "0", "important");
                    node.style.setProperty("pointer-events", "none", "important");
                });
            }

            function hideAllStreamlitSidebarToggles() {
                const selectors = [
                    '[data-testid="stSidebarCollapseButton"]',
                    '[data-testid="stSidebarHeader"] button',
                    'header[data-testid="stHeader"] [data-testid="stSidebarCollapseButton"]',
                    'header[data-testid="stHeader"] button[kind="header"]',
                    '[data-testid="collapsedControl"]',
                    '[data-testid="stSidebarCollapsedControl"]',
                ];
                selectors.forEach((sel) => {
                    doc.querySelectorAll(sel).forEach((node) => {
                        if (node.id === "agentic-sidebar-toggle-btn" || isInSidebarContent(node)) return;
                        hideNativeToggle(node.tagName === "BUTTON" ? node : node.querySelector("button") || node);
                    });
                });
            }

            function resetSidebarContentVisibility() {
                const sidebar = doc.querySelector('section[data-testid="stSidebar"]');
                if (!sidebar) return;
                const props = ["display", "visibility", "opacity", "width", "height", "overflow", "pointer-events", "max-height", "min-height", "max-width", "min-width", "padding", "margin"];
                sidebar.querySelectorAll(":scope > div").forEach((wrap) => {
                    ["overflow", "max-width"].forEach((p) => wrap.style.removeProperty(p));
                });
                sidebar.querySelectorAll(
                    '[data-testid="stSidebarContent"], [data-testid="stSidebarUserContent"], [data-testid="stAppViewBlockContainer"], [data-testid="stElementContainer"], [data-testid="stMarkdownContainer"], [data-testid="stVerticalBlock"], [data-testid="stButton"], [data-testid="stMarkdown"], div[data-testid="stAlert"], div[data-testid="stExpander"], .side-brand-row, .side-section-label, .side-sidebar-layout, .side-sidebar-main, .side-sidebar-lower, .side-footer, .side-footer-anchor'
                ).forEach((el) => {
                    props.forEach((p) => el.style.removeProperty(p));
                });
            }

            function forceSidebarContentVisible() {
                const content = doc.querySelector('section[data-testid="stSidebar"] [data-testid="stSidebarContent"]');
                if (!content) return;
                content.style.setProperty("display", "flex", "important");
                content.style.setProperty("visibility", "visible", "important");
                content.style.setProperty("opacity", "1", "important");
                content.style.setProperty("pointer-events", "auto", "important");
                content.style.setProperty("height", "100vh", "important");
                content.style.setProperty("width", "100%", "important");
                content.style.setProperty("overflow", "hidden", "important");
            }

            function forceSidebarContentHidden() {
                const sidebar = doc.querySelector('section[data-testid="stSidebar"]');
                if (!sidebar) return;
                const hideProps = [
                    ["display", "none"],
                    ["visibility", "hidden"],
                    ["opacity", "0"],
                    ["pointer-events", "none"],
                    ["width", "0"],
                    ["min-width", "0"],
                    ["max-width", "0"],
                    ["height", "0"],
                    ["min-height", "0"],
                    ["max-height", "0"],
                    ["overflow", "hidden"],
                    ["padding", "0"],
                    ["margin", "0"],
                ];
                const applyHide = (el) => {
                    hideProps.forEach(([p, v]) => el.style.setProperty(p, v, "important"));
                };
                sidebar.querySelectorAll(
                    '[data-testid="stSidebarContent"], [data-testid="stSidebarUserContent"], [data-testid="stAppViewBlockContainer"], [data-testid="stElementContainer"], [data-testid="stMarkdownContainer"], [data-testid="stVerticalBlock"], [data-testid="stButton"], [data-testid="stMarkdown"], div[data-testid="stAlert"], div[data-testid="stExpander"], .side-brand-row, .side-section-label, .side-sidebar-layout, .side-sidebar-main, .side-sidebar-lower, .side-footer, .side-footer-anchor'
                ).forEach(applyHide);
                sidebar.querySelectorAll(":scope > div").forEach((wrap) => {
                    wrap.style.setProperty("overflow", "hidden", "important");
                    wrap.style.setProperty("max-width", RAIL_PX + "px", "important");
                });
            }

            function tryAutoExpandOnce() {
                if (api.autoExpandTried) return;
                api.autoExpandTried = true;
                const sb = doc.querySelector('section[data-testid="stSidebar"]');
                if (sb && sb.getAttribute("aria-expanded") === "false") {
                    win.setTimeout(() => clickNativeExpand(), 120);
                }
            }

            function hideSidebarHeaderSpacer() {
                doc.querySelectorAll('[data-testid="stSidebarHeader"]').forEach((el) => {
                    el.style.setProperty("display", "none", "important");
                    el.style.setProperty("height", "0", "important");
                    el.style.setProperty("min-height", "0", "important");
                    el.style.setProperty("max-height", "0", "important");
                    el.style.setProperty("margin", "0", "important");
                    el.style.setProperty("padding", "0", "important");
                    el.style.setProperty("overflow", "hidden", "important");
                });
            }

            function pullSidebarContentUp() {
                const sidebar = doc.querySelector('section[data-testid="stSidebar"]');
                const content = sidebar?.querySelector('[data-testid="stSidebarContent"]');
                const anchor = content?.querySelector(".side-brand-row") || content?.firstElementChild;
                if (!sidebar || !content || !anchor) return;
                const gap = anchor.getBoundingClientRect().top - sidebar.getBoundingClientRect().top;
                const target = 6;
                if (gap > target + 2) {
                    content.style.setProperty("margin-top", (target - gap) + "px", "important");
                } else {
                    content.style.setProperty("margin-top", "0", "important");
                }
            }

            function syncToggles() {
                hideSidebarHeaderSpacer();
                hideAllStreamlitSidebarToggles();
                const sidebar = doc.querySelector('section[data-testid="stSidebar"]');
                const expanded = isExpanded();
                doc.body.classList.toggle("agentic-sidebar-expanded", expanded);
                doc.body.classList.toggle("agentic-sidebar-collapsed", !expanded);
                const slot = doc.querySelector('section[data-testid="stSidebar"] .side-collapse-slot');
                const collapseBtn = nativeCollapseBtn();
                const expandBtn = nativeExpandBtn();
                const size = 44;
                const railTop = 10;
                const railLeft = Math.max(0, (RAIL_PX - size) / 2);

                hideNativeToggle(collapseBtn);
                hideNativeToggle(expandBtn);
                unpinButton(collapseBtn);
                unpinButton(expandBtn);

                if (expanded) {
                    resetSidebarContentVisibility();
                    forceSidebarContentVisible();
                    if (sidebar) {
                        sidebar.style.removeProperty("width");
                        sidebar.style.removeProperty("min-width");
                        sidebar.style.removeProperty("max-width");
                    }
                    fallback.title = "收起侧边栏";
                    fallback.textContent = "\\u2039";
                    pullSidebarContentUp();
                    win.setTimeout(pullSidebarContentUp, 80);
                    if (slot) {
                        const rect = slot.getBoundingClientRect();
                        const pinSize = Math.max(rect.width, size);
                        const top = rect.height > 0 ? rect.top : railTop;
                        const left = rect.width > 0 ? rect.left : (sidebar.getBoundingClientRect().width - pinSize - 12);
                        pinButton(fallback, top, left, pinSize);
                        fallback.style.setProperty("display", "inline-flex", "important");
                    } else {
                        fallback.style.setProperty("display", "none", "important");
                    }
                } else {
                    fallback.title = "展开侧边栏";
                    fallback.textContent = "\\u203A";
                    showExpandControlShell();
                    forceSidebarContentHidden();
                    pinButton(fallback, railTop, railLeft, size);
                    fallback.style.setProperty("display", "inline-flex", "important");
                }
            }

            let syncScheduled = false;
            function scheduleSync() {
                if (syncScheduled) return;
                syncScheduled = true;
                requestAnimationFrame(() => {
                    syncScheduled = false;
                    syncToggles();
                });
            }

            api.scheduleSync = scheduleSync;
            api.syncToggles = syncToggles;
            api.clickNativeExpand = clickNativeExpand;

            scheduleSync();
            tryAutoExpandOnce();
            [50, 200, 600, 1500].forEach((ms) => win.setTimeout(scheduleSync, ms));
            win.setTimeout(tryAutoExpandOnce, 400);
            if (!api.bound) {
                api.bound = true;
                win.addEventListener("resize", scheduleSync, { passive: true });
                new MutationObserver(scheduleSync).observe(doc.body, {
                    childList: true,
                    subtree: true,
                    attributes: true,
                    attributeFilter: ["aria-expanded", "class", "style"],
                });
            }
        })();
        </script>
        """,
        height=0,
    )


def inject_style() -> None:
    st.markdown(
        """
        <style>
        :root {
            --soft-bg: #f7f3ee;
            --panel-bg: #fffdf8;
            --panel-border: #eadfd2;
            --text-main: #334155;
            --text-muted: #7c8a9a;
            --accent: #4f8f8b;
            --accent-soft: #e6f2ef;
            --sidebar-width: 21.5rem;
            --sidebar-rail: 2.75rem;
        }
        .stApp {
            background:
                radial-gradient(circle at 10% 8%, rgba(223, 239, 235, .9), transparent 28rem),
                linear-gradient(180deg, #fbf8f3 0%, #f7f3ee 100%);
        }
        .main .block-container {
            padding-top: 0 !important;
            padding-bottom: 1.3rem;
            padding-left: 1rem;
            padding-right: 1rem;
            max-width: 100%;
        }
        [data-testid="stMainBlockContainer"] {
            padding-top: 0 !important;
            padding-left: 1rem;
            padding-right: 1rem;
        }
        section.main { padding-top: 0 !important; }

        /* —— 仅侧边栏布局与视觉 —— */
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #fbf7f1 0%, #f4efe8 100%) !important;
            border-right: 1px solid #eadfd2 !important;
            top: 0 !important;
            padding-top: 0 !important;
            margin-top: 0 !important;
        }
        body.agentic-sidebar-expanded section[data-testid="stSidebar"],
        section[data-testid="stSidebar"][aria-expanded="true"] {
            width: var(--sidebar-width) !important;
            min-width: var(--sidebar-width) !important;
        }
        /* 去掉 Streamlit 顶栏占位，避免展开后顶部大块空白 */
        [data-testid="stSidebarHeader"],
        section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] {
            display: none !important;
            height: 0 !important;
            min-height: 0 !important;
            max-height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            overflow: hidden !important;
            border: none !important;
        }
        /* 隐藏 Streamlit 原生 << / >>，仅保留右侧自定义折叠钮 */
        [data-testid="stSidebarCollapseButton"],
        [data-testid="stSidebarCollapseButton"] button,
        [data-testid="stSidebarHeader"] button,
        header[data-testid="stHeader"] [data-testid="stSidebarCollapseButton"],
        header[data-testid="stHeader"] button[kind="header"],
        [data-testid="collapsedControl"],
        [data-testid="collapsedControl"] button,
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="stSidebarCollapsedControl"] button {
            display: none !important;
            visibility: hidden !important;
            opacity: 0 !important;
            pointer-events: none !important;
            width: 0 !important;
            height: 0 !important;
            overflow: hidden !important;
            position: absolute !important;
            left: -9999px !important;
        }
        section[data-testid="stSidebar"] > div {
            padding-top: 0 !important;
            padding-bottom: 0 !important;
            margin-top: 0 !important;
            gap: 0 !important;
        }
        section[data-testid="stSidebar"][aria-expanded="true"] [data-testid="stSidebarContent"] {
            margin-top: 0 !important;
            padding-top: 0 !important;
        }
        div[data-testid="stSidebarNav"] { display: none !important; }
        body.agentic-sidebar-expanded section[data-testid="stSidebar"] [data-testid="stSidebarContent"],
        body.agentic-sidebar-expanded section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"],
        body.agentic-sidebar-expanded section[data-testid="stSidebar"] [data-testid="stAppViewBlockContainer"],
        section[data-testid="stSidebar"][aria-expanded="true"] [data-testid="stSidebarContent"],
        section[data-testid="stSidebar"][aria-expanded="true"] [data-testid="stSidebarUserContent"],
        section[data-testid="stSidebar"][aria-expanded="true"] [data-testid="stAppViewBlockContainer"] {
            display: flex !important;
            flex-direction: column !important;
            padding: 0 .5rem 0 !important;
            margin-top: 0 !important;
            visibility: visible !important;
            opacity: 1 !important;
            min-height: 100vh !important;
            max-height: 100vh !important;
            height: 100vh !important;
            box-sizing: border-box !important;
            pointer-events: auto !important;
            overflow: hidden !important;
        }
        body.agentic-sidebar-expanded section[data-testid="stSidebar"] .side-sidebar-layout {
            display: flex !important;
            flex-direction: column !important;
            flex: 1 1 auto !important;
            width: 100% !important;
            min-height: 0 !important;
            box-sizing: border-box !important;
        }
        body.agentic-sidebar-expanded section[data-testid="stSidebar"] .side-sidebar-main {
            flex: 1 1 auto !important;
            width: 100% !important;
            min-height: 0 !important;
            overflow-x: hidden !important;
            overflow-y: auto !important;
            padding-bottom: .25rem !important;
        }
        body.agentic-sidebar-expanded section[data-testid="stSidebar"] .side-sidebar-lower {
            flex-shrink: 0 !important;
            width: 100% !important;
            margin-top: auto !important;
            padding-top: .55rem !important;
            padding-bottom: 0 !important;
            box-sizing: border-box !important;
        }
        body.agentic-sidebar-expanded section[data-testid="stSidebar"] {
            width: var(--sidebar-width) !important;
            min-width: var(--sidebar-width) !important;
            max-width: var(--sidebar-width) !important;
        }
        body.agentic-sidebar-expanded section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
            display: flex !important;
            flex-direction: column !important;
            visibility: visible !important;
            opacity: 1 !important;
            width: 100% !important;
            min-height: 100vh !important;
            max-height: 100vh !important;
            height: 100vh !important;
            overflow: hidden !important;
            pointer-events: auto !important;
        }
        body.agentic-sidebar-expanded section[data-testid="stSidebar"] [data-testid="stSidebarContent"] > [data-testid="stVerticalBlock"] {
            display: flex !important;
            flex-direction: column !important;
            flex: 1 1 auto !important;
            width: 100% !important;
            min-height: 0 !important;
            gap: .35rem !important;
            padding-top: 0 !important;
            margin-top: 0 !important;
        }
        section[data-testid="stSidebar"] .side-footer-anchor {
            margin-top: 0 !important;
            padding-top: .25rem !important;
            padding-bottom: 0 !important;
            width: 100% !important;
        }
        section[data-testid="stSidebar"] .side-brand-row + [data-testid="stElementContainer"],
        section[data-testid="stSidebar"] .side-brand-row + div {
            margin-top: 1.45rem !important;
        }
        section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
            gap: .45rem !important;
        }
        section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div {
            padding-top: 0 !important;
        }
        section[data-testid="stSidebar"] [data-testid="stElementContainer"]:first-of-type,
        section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"]:first-of-type {
            margin-top: 0 !important;
            padding-top: 0 !important;
        }
        section[data-testid="stSidebar"] .side-brand-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: .5rem;
            min-height: 2.4rem;
            margin: 0 0 .45rem 0;
            padding: 0;
        }
        section[data-testid="stSidebar"] .side-brand-title {
            font-size: 1.18rem;
            font-weight: 700;
            color: #334155;
            margin: 0;
            line-height: 1.25;
            flex: 1 1 auto;
            min-width: 0;
            letter-spacing: -.01em;
        }
        section[data-testid="stSidebar"] .side-collapse-slot {
            width: 2.75rem;
            height: 2.75rem;
            flex: 0 0 2.75rem;
            visibility: hidden;
            pointer-events: none;
        }
        section[data-testid="stSidebar"] [data-testid="stElementContainer"],
        section[data-testid="stSidebar"] [data-testid="stButton"],
        section[data-testid="stSidebar"] [data-testid="stButton"] > div,
        section[data-testid="stSidebar"] .stButton {
            width: 100% !important;
            max-width: 100% !important;
            margin-left: 0 !important;
            margin-right: 0 !important;
        }
        section[data-testid="stSidebar"] [data-testid="stButton"],
        section[data-testid="stSidebar"] [data-testid="stButton"] > div {
            margin-top: 0 !important;
            margin-bottom: 0 !important;
            padding: 0 !important;
        }
        section[data-testid="stSidebar"] .stButton > button p {
            padding: 0 !important;
            margin: 0 !important;
        }
        section[data-testid="stSidebar"] [data-testid="stMarkdown"] p {
            margin: 0 !important;
        }
        section[data-testid="stSidebar"] .side-section-label {
            font-size: .75rem;
            font-weight: 600;
            color: #94a3b8;
            margin: .12rem 0 .22rem 0;
            letter-spacing: .03em;
            width: 100% !important;
        }
        section[data-testid="stSidebar"] .side-sidebar-main .side-section-label {
            margin-top: .25rem;
        }
        section[data-testid="stSidebar"] .side-example-list [data-testid="stVerticalBlock"] {
            gap: .2rem !important;
        }
        section[data-testid="stSidebar"] .side-example-list .stButton > button {
            font-size: .84rem !important;
            line-height: 1.35 !important;
            padding: .38rem .65rem !important;
            white-space: normal !important;
            text-align: left !important;
            justify-content: flex-start !important;
            min-height: 2.1rem !important;
            width: 100% !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stAlert"] {
            width: 100% !important;
            box-sizing: border-box !important;
            border-radius: 8px !important;
            margin-bottom: .3rem !important;
            padding: .4rem .6rem !important;
            box-shadow: none !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stExpander"] {
            border: none !important;
            border-radius: 8px !important;
            background: transparent !important;
            margin-bottom: .25rem !important;
            box-shadow: none !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stExpander"] summary {
            padding: .35rem 0 !important;
        }
        section[data-testid="stSidebar"] .stButton > button {
            border-radius: 8px !important;
            border: 1px solid #e5dbd0 !important;
            box-shadow: none !important;
            outline: none !important;
            background: rgba(255, 253, 248, .6) !important;
            color: #475569 !important;
            font-size: .875rem !important;
            padding: .38rem .65rem !important;
            min-height: 2rem !important;
            width: 100% !important;
            max-width: 100% !important;
            box-sizing: border-box !important;
        }
        section[data-testid="stSidebar"] .stButton > button:hover,
        section[data-testid="stSidebar"] .stButton > button:focus {
            border-color: #c9d9d6 !important;
            box-shadow: none !important;
            outline: none !important;
            color: #2f6f6a !important;
            background: rgba(241, 250, 247, .95) !important;
        }
        section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
            background: rgba(230, 242, 239, .85) !important;
            border-color: rgba(79, 143, 139, .32) !important;
            color: #2f6f6a !important;
            font-weight: 600 !important;
        }
        section[data-testid="stSidebar"] .stCaption {
            color: #7c8a9a !important;
            font-size: .78rem !important;
        }
        section[data-testid="stSidebar"] .side-thread-list [data-testid="stVerticalBlock"] {
            gap: .15rem !important;
        }
        section[data-testid="stSidebar"] .side-thread-list .stButton > button {
            text-align: left !important;
            justify-content: flex-start !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            white-space: nowrap !important;
            padding: .36rem .65rem !important;
            width: 100% !important;
        }
        section[data-testid="stSidebar"] .side-footer {
            margin-top: 0;
            padding-top: .2rem;
            padding-bottom: 0;
            border-top: 1px solid #e8dfd4;
            width: 100% !important;
        }
        section[data-testid="stSidebar"] .side-footer .stButton > button {
            margin-bottom: 0 !important;
        }

        /* 侧边栏折叠：保留原生按钮可见 + 收起后窄条 */
        header[data-testid="stHeader"] {
            background: transparent !important;
            box-shadow: none !important;
            height: 0 !important;
            min-height: 0 !important;
            overflow: visible !important;
            border: none !important;
        }
        header[data-testid="stHeader"] > div {
            height: 0 !important;
            min-height: 0 !important;
            overflow: visible !important;
            padding: 0 !important;
            background: transparent !important;
        }
        div[data-testid="stToolbar"],
        div[data-testid="stDecoration"],
        div[data-testid="stStatusWidget"],
        #MainMenu, footer { display: none !important; }
        /* 仅自定义折叠/展开钮（由 JS 对齐到品牌行右侧 slot） */
        #agentic-sidebar-toggle-btn,
        .agentic-sidebar-toggle-fallback {
            position: fixed !important;
            top: 10px !important;
            left: calc((var(--sidebar-rail) - 2.75rem) / 2) !important;
            z-index: 999999 !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            width: 2.75rem !important;
            height: 2.75rem !important;
            min-width: 2.75rem !important;
            min-height: 2.75rem !important;
            padding: 0 !important;
            margin: 0 !important;
            border: none !important;
            outline: none !important;
            border-radius: 6px !important;
            background: transparent !important;
            color: #64748b !important;
            box-shadow: none !important;
            font-size: 1.5rem !important;
            line-height: 1 !important;
            cursor: pointer !important;
        }
        #agentic-sidebar-toggle-btn:hover {
            border: none !important;
            background: rgba(79, 143, 139, .1) !important;
            color: #2f6f6a !important;
            box-shadow: none !important;
        }
        section[data-testid="stSidebar"][aria-expanded="false"],
        body.agentic-sidebar-collapsed section[data-testid="stSidebar"] {
            width: var(--sidebar-rail) !important;
            min-width: var(--sidebar-rail) !important;
            max-width: var(--sidebar-rail) !important;
            min-height: 100vh !important;
            transform: none !important;
            translate: none !important;
            background: linear-gradient(180deg, #fbf7f1 0%, #f4efe8 100%) !important;
            border-right: 1px solid #eadfd2 !important;
            overflow: hidden !important;
        }
        body.agentic-sidebar-collapsed section[data-testid="stSidebar"] > div,
        section[data-testid="stSidebar"][aria-expanded="false"] > div,
        body.agentic-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="stSidebarContent"],
        body.agentic-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"],
        body.agentic-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="stAppViewBlockContainer"],
        section[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarContent"],
        section[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarUserContent"],
        section[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stAppViewBlockContainer"] {
            display: none !important;
            visibility: hidden !important;
            opacity: 0 !important;
            pointer-events: none !important;
            width: 0 !important;
            min-width: 0 !important;
            max-width: 0 !important;
            height: 0 !important;
            min-height: 0 !important;
            max-height: 0 !important;
            padding: 0 !important;
            margin: 0 !important;
            overflow: hidden !important;
            clip: rect(0, 0, 0, 0) !important;
            position: absolute !important;
            left: -9999px !important;
        }
        body.agentic-sidebar-collapsed section[data-testid="stSidebar"] .side-brand-row,
        body.agentic-sidebar-collapsed section[data-testid="stSidebar"] .side-section-label,
        body.agentic-sidebar-collapsed section[data-testid="stSidebar"] .side-sidebar-layout,
        body.agentic-sidebar-collapsed section[data-testid="stSidebar"] .side-sidebar-main,
        body.agentic-sidebar-collapsed section[data-testid="stSidebar"] .side-sidebar-lower,
        body.agentic-sidebar-collapsed section[data-testid="stSidebar"] .side-footer,
        body.agentic-sidebar-collapsed section[data-testid="stSidebar"] .side-footer-anchor,
        section[data-testid="stSidebar"][aria-expanded="false"] .side-brand-row,
        section[data-testid="stSidebar"][aria-expanded="false"] .side-section-label,
        section[data-testid="stSidebar"][aria-expanded="false"] .side-sidebar-layout,
        section[data-testid="stSidebar"][aria-expanded="false"] .side-sidebar-main,
        section[data-testid="stSidebar"][aria-expanded="false"] .side-sidebar-lower,
        section[data-testid="stSidebar"][aria-expanded="false"] .side-footer,
        section[data-testid="stSidebar"][aria-expanded="false"] .side-footer-anchor {
            display: none !important;
            visibility: hidden !important;
        }
        body.agentic-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="stElementContainer"],
        body.agentic-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
        body.agentic-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="stMarkdown"],
        body.agentic-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="stVerticalBlock"],
        body.agentic-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"],
        body.agentic-sidebar-collapsed section[data-testid="stSidebar"] [data-testid="stButton"],
        body.agentic-sidebar-collapsed section[data-testid="stSidebar"] div[data-testid="stAlert"],
        body.agentic-sidebar-collapsed section[data-testid="stSidebar"] div[data-testid="stExpander"],
        section[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stElementContainer"],
        section[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stMarkdownContainer"],
        section[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stMarkdown"],
        section[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stVerticalBlock"],
        section[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stVerticalBlockBorderWrapper"],
        section[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stButton"],
        section[data-testid="stSidebar"][aria-expanded="false"] div[data-testid="stAlert"],
        section[data-testid="stSidebar"][aria-expanded="false"] div[data-testid="stExpander"] {
            display: none !important;
            visibility: hidden !important;
            pointer-events: none !important;
        }
        section[data-testid="stSidebar"][aria-expanded="false"] + section.main,
        body.agentic-sidebar-collapsed section[data-testid="stSidebar"] + section.main {
            margin-left: var(--sidebar-rail) !important;
            width: calc(100% - var(--sidebar-rail)) !important;
            max-width: calc(100% - var(--sidebar-rail)) !important;
        }
        section[data-testid="stSidebar"][aria-expanded="false"] + section.main .block-container,
        section[data-testid="stSidebar"][aria-expanded="false"] + section.main [data-testid="stMainBlockContainer"],
        body.agentic-sidebar-collapsed section[data-testid="stSidebar"] + section.main .block-container,
        body.agentic-sidebar-collapsed section[data-testid="stSidebar"] + section.main [data-testid="stMainBlockContainer"] {
            padding-left: 1rem !important;
        }
        body.agentic-sidebar-collapsed #agentic-sidebar-toggle-btn,
        body:not(.agentic-sidebar-expanded) #agentic-sidebar-toggle-btn {
            visibility: visible !important;
            opacity: 1 !important;
            pointer-events: auto !important;
        }
        /* —— 主区原版样式 —— */
        .hero {
            padding: 1rem 1.25rem;
            border-radius: 22px;
            background: linear-gradient(135deg, #fffaf2 0%, #e8f3f0 52%, #eaf0fb 100%);
            color: #334155;
            border: 1px solid rgba(226, 213, 198, .9);
            box-shadow: 0 16px 38px rgba(100, 116, 139, .12);
            margin-bottom: .85rem;
        }
        .hero h1 {
            font-size: 1.6rem;
            line-height: 1.25;
            margin: 0 0 .35rem 0;
            letter-spacing: -.02em;
        }
        .hero p { opacity: .82; margin: 0; font-size: .96rem; }
        .soft-card {
            border: 1px solid var(--panel-border);
            border-radius: 18px;
            padding: .95rem 1rem;
            background: rgba(255, 253, 248, .88);
            box-shadow: 0 10px 26px rgba(100, 116, 139, .08);
            margin-bottom: .85rem;
        }
        .soft-card h3 {
            margin: 0 0 .35rem 0;
            font-size: 1.05rem;
            color: var(--text-main);
        }
        .soft-card p { margin: 0; color: var(--text-muted); font-size: .9rem; }
        .answer-card {
            border: 1px solid rgba(79, 143, 139, .28);
            border-left: 6px solid #6aa8a2;
            border-radius: 18px;
            padding: 1rem 1.1rem;
            background: linear-gradient(180deg, rgba(246, 252, 249, .96), rgba(255, 253, 248, .94));
            box-shadow: 0 12px 28px rgba(79, 143, 139, .10);
            margin: .65rem 0 1rem 0;
        }
        .answer-label {
            font-size: .82rem;
            color: #5c6a79;
            margin-bottom: .55rem;
        }
        .answer-body {
            font-size: 1.02rem;
            color: #1f2937;
            line-height: 1.55;
        }
        .section-title {
            margin: .1rem 0 .55rem 0;
            font-size: 1.08rem;
            font-weight: 700;
            color: #334155;
        }
        .badge-row {
            display: flex;
            flex-wrap: wrap;
            gap: .45rem;
            margin-top: .6rem;
        }
        .badge {
            padding: .28rem .55rem;
            border-radius: 999px;
            background: rgba(79, 143, 139, .12);
            color: #346b68;
            font-size: .78rem;
            border: 1px solid rgba(79, 143, 139, .18);
        }
        section.main div[data-testid="stMetric"] {
            background: rgba(255, 253, 248, .9);
            border: 1px solid #eadfd2;
            border-radius: 16px;
            padding: .65rem .75rem;
            box-shadow: 0 8px 18px rgba(100, 116, 139, .07);
        }
        section.main div[data-testid="stMetricValue"] {
            color: #3f7774;
            font-size: 1.45rem;
        }
        section.main div[data-testid="stAlert"] {
            border-radius: 16px;
            border: 1px solid rgba(226, 213, 198, .85);
        }
        section.main .stButton > button {
            border-radius: 12px;
            border: 1px solid #d8cbbd;
            background: #fffdf8;
            color: #475569;
        }
        section.main .stButton > button:hover {
            border-color: #79aaa6;
            color: #2f6f6a;
            background: #f1faf7;
        }
        section.main .stButton > button[kind="primary"],
        section.main .stButton > button[data-testid="baseButton-primary"],
        section.main button[kind="primary"],
        section.main button[data-testid="baseButton-primary"],
        section[data-testid="stMain"] .stButton > button[kind="primary"],
        section[data-testid="stMain"] .stButton > button[data-testid="baseButton-primary"],
        section[data-testid="stMain"] button[kind="primary"],
        section[data-testid="stMain"] button[data-testid="baseButton-primary"],
        [data-testid="stAppViewContainer"] [data-testid="stMain"] .stButton > button[kind="primary"],
        [data-testid="stAppViewContainer"] [data-testid="stMain"] .stButton > button[data-testid="baseButton-primary"] {
            background: #3f9d6b !important;
            background-color: #3f9d6b !important;
            border-color: #2f8a5a !important;
            color: #f7fff9 !important;
            font-weight: 700;
            box-shadow: 0 10px 22px rgba(63, 157, 107, .22) !important;
        }
        section.main .stButton > button[kind="primary"]:hover,
        section.main .stButton > button[kind="primary"]:focus,
        section.main .stButton > button[data-testid="baseButton-primary"]:hover,
        section.main .stButton > button[data-testid="baseButton-primary"]:focus,
        section.main button[kind="primary"]:hover,
        section.main button[kind="primary"]:focus,
        section.main button[data-testid="baseButton-primary"]:hover,
        section.main button[data-testid="baseButton-primary"]:focus,
        section[data-testid="stMain"] .stButton > button[kind="primary"]:hover,
        section[data-testid="stMain"] .stButton > button[kind="primary"]:focus,
        section[data-testid="stMain"] .stButton > button[data-testid="baseButton-primary"]:hover,
        section[data-testid="stMain"] .stButton > button[data-testid="baseButton-primary"]:focus,
        section[data-testid="stMain"] button[kind="primary"]:hover,
        section[data-testid="stMain"] button[kind="primary"]:focus,
        section[data-testid="stMain"] button[data-testid="baseButton-primary"]:hover,
        section[data-testid="stMain"] button[data-testid="baseButton-primary"]:focus,
        [data-testid="stAppViewContainer"] [data-testid="stMain"] .stButton > button[kind="primary"]:hover,
        [data-testid="stAppViewContainer"] [data-testid="stMain"] .stButton > button[kind="primary"]:focus,
        [data-testid="stAppViewContainer"] [data-testid="stMain"] .stButton > button[data-testid="baseButton-primary"]:hover,
        [data-testid="stAppViewContainer"] [data-testid="stMain"] .stButton > button[data-testid="baseButton-primary"]:focus {
            background: #2f8a5a !important;
            background-color: #2f8a5a !important;
            border-color: #24724a !important;
            color: #f1fff6 !important;
        }
        section.main .stTextArea textarea,
        section.main [data-testid="stTextArea"] textarea,
        section.main div[data-testid="stTextArea"] textarea {
            border-radius: 16px;
            border: 1px solid #eadfd2 !important;
            background: #fff2e6 !important;
            color: #3b4a5a;
            font-size: .98rem;
            line-height: 1.6;
            padding: .7rem .85rem;
            box-shadow: 0 10px 20px rgba(100, 116, 139, .08) !important;
            transition: border-color .2s ease, box-shadow .2s ease;
        }
        section.main .stTextArea textarea:focus,
        section.main [data-testid="stTextArea"] textarea:focus,
        section.main div[data-testid="stTextArea"] textarea:focus {
            border-color: #79aaa6 !important;
            box-shadow: 0 0 0 3px rgba(121, 170, 166, .18) !important;
        }
        section.main .stTextArea textarea::placeholder {
            color: #93a2b1;
        }
        section.main div[data-testid="stExpander"] {
            border: 1px solid #eadfd2;
            border-radius: 16px;
            background: rgba(255, 253, 248, .74);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def run_agent(query: str, thread_id: str) -> dict:
    """运行单轮分析；thread_id 仅用于兼容界面会话记录，不传入 Agent 状态。"""
    _ = thread_id
    result = get_compiled_graph().invoke(
        {"user_query": query, "messages": [("user", query)]},
    )
    if result.get("chart_paths"):
        result = dict(result)
        result["chart_paths"] = normalize_chart_paths(result["chart_paths"])
    return result


def ensure_sidebar_toggle_scripts() -> None:
    """每次 rerun 执行轻量 sync，避免 DOM 重建后展开钮消失。"""
    inject_sidebar_toggle_scripts()


def result_dataframe(result: dict) -> pd.DataFrame | None:
    rows = result.get("data_rows") or []
    columns = result.get("data_columns") or []
    if rows:
        return pd.DataFrame(rows, columns=columns or None)
    return None


def result_dataframes(result: dict) -> list[tuple[str, pd.DataFrame]]:
    data_results = result.get("data_results") or []
    frames: list[tuple[str, pd.DataFrame]] = []
    for idx, item in enumerate(data_results, start=1):
        rows = item.get("rows") or []
        columns = item.get("columns") or []
        if rows:
            title = item.get("question") or f"问题{idx}"
            frames.append((title, pd.DataFrame(rows, columns=columns or None)))
    if not frames:
        df = result_dataframe(result)
        if df is not None:
            frames.append(("本轮结果", df))
    return frames


def answer_text(result: dict) -> str:
    return (result.get("final_answer") or result.get("data_summary") or "").strip()


def render_answer_card(text: str) -> None:
    if not text:
        return
    safe_text = html.escape(text).replace("\n", "<br/>")
    st.markdown(
        f"""
        <div class="answer-card">
          <div class="answer-label">答案 · 本轮答案</div>
          <div class="answer-body">{safe_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def init_threads() -> None:
    if "threads" not in st.session_state:
        st.session_state.threads = {
            "demo-thread-1": {
                "title": "新对话",
                "chat_history": [],
                "last_result": {},
                "query_text": "",
            }
        }
    if "current_thread_id" not in st.session_state:
        st.session_state.current_thread_id = next(iter(st.session_state.threads))


def get_current_thread() -> dict:
    init_threads()
    thread_id = st.session_state.current_thread_id
    return st.session_state.threads[thread_id]


def query_key(thread_id: str) -> str:
    return f"query_text_{thread_id}"


def create_new_thread() -> str:
    new_id = f"thread-{uuid.uuid4().hex[:8]}"
    st.session_state.threads[new_id] = {
        "title": "新对话",
        "chat_history": [],
        "last_result": {},
        "query_text": "",
    }
    st.session_state.current_thread_id = new_id
    return new_id


def delete_current_thread() -> None:
    current_id = st.session_state.current_thread_id
    st.session_state.threads.pop(current_id, None)
    st.session_state.pop(query_key(current_id), None)
    if st.session_state.threads:
        st.session_state.current_thread_id = next(iter(st.session_state.threads))
    else:
        create_new_thread()


def render_sidebar(ok: bool, missing: list[str]) -> None:
    """主流 LLM 侧边栏结构：顶栏品牌 → 新对话 → 会话列表 → 示例 → 底部固定区。"""
    current_id = st.session_state.current_thread_id
    thread = get_current_thread()

    st.markdown('<div class="side-sidebar-layout">', unsafe_allow_html=True)

    st.markdown(
        """
        <div class="side-brand-row">
          <div class="side-brand-title">Agentic BI</div>
          <div class="side-collapse-slot" aria-hidden="true"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("＋ 新对话", key="sidebar_new_chat", width="stretch"):
        create_new_thread()
        st.rerun()

    st.markdown('<div class="side-sidebar-main">', unsafe_allow_html=True)
    st.markdown('<div class="side-section-label">历史对话</div>', unsafe_allow_html=True)
    thread_ids = list(st.session_state.threads.keys())
    with st.container(height=365, border=False):
        st.markdown('<div class="side-thread-list">', unsafe_allow_html=True)
        for tid in reversed(thread_ids):
            title = st.session_state.threads[tid]["title"]
            if len(title) > 24:
                title = title[:24] + "…"
            is_active = tid == current_id
            if st.button(
                title,
                key=f"thread_pick_{tid}",
                width="stretch",
                type="primary" if is_active else "secondary",
            ) and not is_active:
                st.session_state.current_thread_id = tid
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="side-sidebar-lower">', unsafe_allow_html=True)
    st.markdown('<div class="side-section-label">示例问题</div>', unsafe_allow_html=True)
    st.markdown('<div class="side-example-list">', unsafe_allow_html=True)
    for q in EXAMPLE_QUESTIONS:
        if st.button(q, key=f"example_{q}", width="stretch"):
            thread["query_text"] = q
            st.session_state[query_key(current_id)] = q
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="side-footer-anchor"><div class="side-footer">', unsafe_allow_html=True)
    if ok:
        st.success("数据集已就绪")
    else:
        st.warning("数据集未就绪")
        with st.expander("数据配置", expanded=False):
            st.caption(str(RAW_DATA_DIR))
            for f in missing:
                st.caption(f"缺少: {f}")

    if st.button("删除当前对话", key="sidebar_delete_chat", width="stretch"):
        delete_current_thread()
        st.rerun()
    st.markdown("</div></div></div></div>", unsafe_allow_html=True)


def submit_query(prompt: str, thread_id: str, data_ready: bool) -> str:
    prompt = prompt.strip()
    if not prompt:
        return "请输入一个业务问题。"

    thread = st.session_state.threads[thread_id]
    thread["chat_history"].append(("user", prompt))
    thread["query_text"] = prompt
    if len(thread["chat_history"]) == 1:
        thread["title"] = prompt[:24] + ("…" if len(prompt) > 24 else "")
    if not data_ready:
        reply = "数据集未就绪，请先完成 db_init → etl → refresh_views。"
        thread["chat_history"].append(("assistant", reply))
        return reply

    try:
        with st.spinner("多智能体正在分析：查询数据、生成图表、输出策略..."):
            result = run_agent(prompt, thread_id=thread_id)
            thread["last_result"] = result
            reply = answer_text(result) or "已完成分析。"
    except Exception as exc:  # noqa: BLE001
        reply = f"执行失败：{exc}"
    thread["chat_history"].append(("assistant", reply))
    return reply


def clear_query_text(key: str, thread_id: str) -> None:
    st.session_state[key] = ""
    st.session_state.threads[thread_id]["query_text"] = ""


st.set_page_config(page_title="Agentic BI — Olist", layout="wide", initial_sidebar_state="expanded")
inject_style()
ensure_sidebar_toggle_scripts()

st.markdown(
    """
    <div class="hero">
      <h1>Agentic BI — Olist 运营分析与决策智能系统</h1>
      <p>面向业务人员的自然语言分析入口，集成预聚合视图加速、预测、What-if 模拟、异常检测与决策建议。</p>
      <div class="badge-row">
        <span class="badge">多 Agent 协作</span>
        <span class="badge">MySQL 预聚合视图</span>
        <span class="badge">9 类可视化</span>
        <span class="badge">单轮问题隔离</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

ok, missing = check_raw_data_files()
init_threads()

with st.sidebar:
    render_sidebar(ok, missing)

ensure_sidebar_toggle_scripts()

thread_id = st.session_state.current_thread_id
thread = get_current_thread()
q_key = query_key(thread_id)
if q_key not in st.session_state:
    st.session_state[q_key] = thread.get("query_text", "")

col_chat, col_viz = st.columns([0.95, 1.35], gap="large")

with col_chat:
    st.markdown(
        '<div class="soft-card"><h3>业务提问</h3>'
        "<p>输入自然语言问题，系统会自动判断使用预聚合视图、基础表回退、预测或决策智能。</p></div>",
        unsafe_allow_html=True,
    )
    st.text_area(
        "输入问题",
        key=q_key,
        height=108,
        placeholder="例如：预测未来6周销售额，并说明哪些州需要重点优化配送。",
        label_visibility="collapsed",
    )
    action_col1, action_col2 = st.columns([0.68, 0.32])
    with action_col1:
        ask_clicked = st.button("开始分析", type="primary", width="stretch", key="btn_start_analysis")
    with action_col2:
        st.button("清空输入", width="stretch", on_click=clear_query_text, args=(q_key, thread_id))
    if ask_clicked:
        submit_query(st.session_state[q_key], thread_id, ok)
        thread["query_text"] = ""
        st.rerun()

    if thread.get("last_result"):
        render_answer_card(answer_text(thread["last_result"]))

    st.markdown("#### 对话记录")
    if not thread["chat_history"]:
        st.caption("尚无对话。可以从左侧示例问题开始，也可以直接输入业务问题。")
    for role, content in thread["chat_history"][-8:]:
        with st.chat_message(role):
            formatted = content.replace("\n", "\n\n")
            if role == "assistant" and not content.startswith("执行失败"):
                st.markdown("**本轮答案**")
                st.markdown(formatted)
            else:
                st.markdown(formatted)

with col_viz:
    st.markdown(
        '<div class="soft-card"><h3>分析驾驶舱</h3>'
        "<p>集中展示本轮查询指标、分析结论、可视化图表、SQL 与加分洞察。</p></div>",
        unsafe_allow_html=True,
    )
    last = thread.get("last_result", {}) or {}
    dfs = result_dataframes(last)

    if last:
        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("生成 SQL", len(last.get("sql_queries", [])))
        kpi2.metric("输出图表", len(last.get("chart_paths", [])))
        kpi3.metric("返回行数", int(last.get("data_row_count", 0)))

    if dfs:
        with st.expander("数据预览", expanded=False):
            for title, df in dfs:
                st.markdown(f"**{title}**")
                st.dataframe(df.head(50), width="stretch")

    if last.get("whatif_insights") or last.get("anomaly_insights"):
        st.markdown('<div class="section-title">加分洞察</div>', unsafe_allow_html=True)
        if last.get("whatif_insights"):
            st.success(last["whatif_insights"])
        if last.get("anomaly_insights"):
            st.warning(last["anomaly_insights"])

    if last.get("sql_queries"):
        with st.expander("本轮 SQL 与查询策略", expanded=True):
            for sql in last["sql_queries"]:
                st.code(sql, language="sql")
            if last.get("query_strategy"):
                st.caption(last["query_strategy"])

    chart_paths = normalize_chart_paths(last.get("chart_paths", []))

    if chart_paths:
        with st.expander("图表结果", expanded=False):
            chart_cols = st.columns(2, gap="large")
            chart_titles = last.get("chart_titles") or []
            for idx, p in enumerate(chart_paths):
                title = chart_titles[idx] if idx < len(chart_titles) else Path(p).stem
                with chart_cols[idx % 2]:
                    st.markdown(f"**{title}**")
                    st.image(p, width="stretch")
            if last.get("visualization_strategy"):
                st.caption(f"图表选择策略：{last['visualization_strategy']}")
    elif last:
        st.caption("本轮未生成可用图表文件。")
    else:
        st.markdown(
            '<div class="soft-card"><h3>等待分析</h3>'
            "<p>提交业务问题后，这里会显示关键指标、图表、SQL 与策略建议。</p></div>",
            unsafe_allow_html=True,
        )
