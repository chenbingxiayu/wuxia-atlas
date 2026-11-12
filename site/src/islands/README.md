# islands 编写纪律

本目录所有 island 为 React 组件，在 Vite 预渲染 + 客户端 hydrate 下运行。

## 第 1 条：全部 hooks 声明（useState/useRef/useEffect/useMemo/useCallback/自定义 useXxx）
## 必须先于任何条件返回 / 提前退出

React 靠调用顺序记录 hooks，加载态早退会让某次渲染少调用后面的 hooks，
hydrate 后数据到达即触发 Minified React error #310（island 永久卡在加载文案）。

```tsx
// 正确：hooks 全部声明在前，早退在后
const locHref = useMemo(() => puzzle ? calc(puzzle) : null, [puzzle]);
if (!puzzle) return <div className="gd-loading">出题中…</div>;

// 错误：早退位于 hooks 之前（初次渲染 7 个 hooks，就绪后 8 个 → #310）
if (!puzzle) return <div className="gd-loading">出题中…</div>;
const locHref = useMemo(() => calc(puzzle), [puzzle]); // puzzle 判空收进 useMemo 内部
```

- 组件顶层出现 `if (...) return ...` 时，先数它后面还有没有 hooks——有即违规。
- 嵌套函数（回调、事件处理器）内的 `return` 不算提前退出，不受此条约束。
- 依赖早退条件的 hook，把条件收进 hook 体内判空（返回 null/默认值），保持依赖数组不变。

## 第 2 条：数据 fetch 一律放 useEffect，SSR 预渲染不得发起请求（island 首帧输出加载态）。

## 第 3 条：不改 island 内既有选题/判定算法口径；样式用组件尾部 `<style>` 块，类名带模块前缀。
