import * as echarts from "echarts";
import "echarts-wordcloud";

// 选项由后端以 JSON 下发，无法携带函数。地理图 tooltip 用 {@GMV} 占位，这里换成真正的函数格式化器。
function patchOption(option) {
  const tt = option && option.tooltip;
  if (tt && typeof tt.formatter === "string" && tt.formatter.includes("{@GMV}")) {
    tt.formatter = (p) => {
      const v = Array.isArray(p.value) ? p.value[2] : p.value;
      return `${p.name}<br/>GMV：${Number(v).toLocaleString()}`;
    };
  }
  return option;
}

export function newChart(el, option) {
  const inst = echarts.init(el, null, { renderer: "canvas" });
  inst.setOption(patchOption(option), true);
  return inst;
}

export function downloadChart(inst, name) {
  const url = inst.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: "#fff" });
  const a = document.createElement("a");
  a.href = url; a.download = (name || "chart").replace(/\s+/g, "_") + ".png"; a.click();
}
