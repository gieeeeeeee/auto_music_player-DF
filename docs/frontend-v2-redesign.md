# 前端规范化改造方案 v2.0

> 文档性质:改造设计稿,实现前评审用
> 范围:`gui/` 前端层,不涉及 core 逻辑

## 1. 现状问题

| # | 问题 | 现状 |
|---|------|------|
| 1 | 窗口不可拉伸 | 自绘无边框窗口后丢失了系统边框,无法拖拽边缘调整大小 |
| 2 | 上传识别页内容区域不够用 | "识别结果"文本框固定高度、校对表格挤在剩余空间,长简谱看不全、校对行一多就滚动疲劳 |
| 3 | 页面滚动条观感弱 | 滚动条存在但较细,长页面上下滑动时缺少明显抓手 |
| 4 | 乐谱库"去演奏"跳转不同步 | 主页面切到了"演奏控制",但侧边栏选中项仍停留在"乐谱库" |
| 5 | 提示框与主题割裂 | 使用系统 QMessageBox,白色原生弹窗与整体暗色琥珀金主题完全不搭 |

## 2. 改造方案

### 2.1 窗口边缘拉伸

无边框窗口下系统边框被移除,需自行实现边缘命中检测:

- **方案**:在 `MainWindow` 实现八方向拉伸。鼠标靠近窗口边缘 ≤ 6px 时进入拉伸模式:
  - `mouseMoveEvent`:按鼠标相对边缘位置切换光标形状(左右 `SizeHorCursor`、上下 `SizeVerCursor`、四角 `SizeFDiagCursor`/`SizeBDiagCursor`),需 `setMouseTracking(True)`
  - `mousePressEvent` 判断顺序:**边缘优先,标题栏拖拽其次**(光标在边缘 6px 内 → 拉伸;在标题栏区域 → 拖动窗口)
  - 拉伸实现:记录按下时的窗口几何与鼠标全局位置,move 时按方向计算新 rect 并 `setGeometry`
  - 子控件遮挡鼠标移动事件问题:给根容器安装 `eventFilter`,把子控件上的移动事件归并到主窗口命中逻辑
- **边界**:最小尺寸保持 `900×600`;最大化时禁用拉伸(双击标题栏还原后恢复)
- 右下角附加大号 `QSizeGrip`(样式化),作为明显的拉伸抓手

### 2.2 上传识别页:识别结果 / 校对表格 副边框拉伸

- **方案**:把"识别结果"卡片与"校对表格"卡片放进一个垂直 `QSplitter`,中间分隔条可拖动调整两者比例:
  - `QSplitter(Qt.Vertical)`,分隔条宽 6px,默认与背景融合,hover 时高亮为品牌琥珀色,拖动手感对齐系统分栏
  - 约束:识别结果最小 120px,校对表格最小 200px
  - 该 splitter 卡片占据上传页的剩余高度(随窗口拉伸增长),不再写死高度
- 上传区(步骤 1)、识别/解析(步骤 2)、保存(步骤 5)保持固定高度,不参与分栏

### 2.3 滚动条强化

- 全局滚动条由 6px 加宽到 10px,默认半透明深色滑块,hover 时提亮(品牌色系的深一档)
- 横向滚动条同步规则
- 长页面(上传识别)底部预留内边距,保证最后一项不被底部状态栏遮挡

### 2.4 乐谱库"去演奏"导航联动

- `LibraryTab.go_play` 信号在 `MainWindow._go_play` 中目前只执行 `stack.setCurrentIndex(2)`
- 改造为:**统一入口走侧边栏** `self.nav.setCurrentRow(2)`——侧边栏选中态与页面堆栈始终一致(`currentRowChanged` 已负责切页,天然联动)
- 后续任何跳转入口一律调用 nav 切换,不再直接切 stack

### 2.5 提示框(AppDialog)重新设计

系统 `QMessageBox` 替换为自绘暗色消息框 `AppDialog`(新增 `gui/widgets.py`):

- **结构**:无边框 `QDialog`,父窗口半透明遮罩,圆角卡片(与 SectionCard 同风格),从上到下:图标圆标 → 标题 → 正文 → 按钮区
- **类型与语义色**:
  | 类型 | 图标 | 主色 | 用途 |
  |------|------|------|------|
  | success | ✓ | `#4ADE80` | 保存成功 |
  | info | i | `#D4A24C` | 一般提示 |
  | warning | ! | `#FBBF24` | 校验提醒 |
  | error | ✕ | `#F87171` | 识别失败/出错 |
  | confirm | ? | `#38BDF8` | 删除确认(双按钮) |
- **统一接口**:
  ```python
  AppDialog.show_info(parent, "标题", "正文")
  AppDialog.show_warning(parent, "标题", "正文")
  AppDialog.show_error(parent, "标题", "正文")
  AppDialog.show_success(parent, "标题", "正文")
  ok = AppDialog.confirm(parent, "标题", "正文")  # 返回 True/False
  ```
- **替换点**:
  | 文件 | 现有调用 |
  |------|----------|
  | gui/upload_tab.py | 识别失败、保存成功、解析失败、表格校验、名称为空等 |
  | gui/library_tab.py | 未选择提示、删除确认 |
  | gui/player_tab.py | 乐谱无数据提示 |
  | gui/settings_tab.py | 测试连接结果、删除供应商确认、保存成功等 |

## 3. 文件变更清单

| 文件 | 变更内容 |
|------|----------|
| gui/main_window.py | 八方向边缘拉伸、eventFilter、QSizeGrip、去演奏联动 nav、最大化时禁拉伸 |
| gui/theme.py | 滚动条加宽与 hover、QSplitter 分隔条、AppDialog 样式 |
| gui/widgets.py | **新增**:AppDialog 组件(遮罩+圆角卡片+语义色图标) |
| gui/upload_tab.py | 识别结果/校对表格放入 QSplitter、QMessageBox → AppDialog |
| gui/library_tab.py | QMessageBox → AppDialog |
| gui/player_tab.py | QMessageBox → AppDialog |
| gui/settings_tab.py | QMessageBox → AppDialog |
| tests/smoke_gui.py | 冒烟覆盖新组件(窗口构建+拉伸常量校验) |

## 4. 验收标准

1. 窗口八个方向均可拖拽拉伸,与标题栏拖动无冲突;最大化时拉伸禁用,还原后恢复
2. 上传识别页"识别结果"与"校对表格"之间出现可拖动分隔条,长简谱可完整铺开
3. 滚动条明显易抓,长页面底部无遮挡
4. 乐谱库点"去演奏":页面与侧边栏选中项同步跳到"演奏控制"
5. 全流程无任何白色系统弹窗,所有提示为暗色语义化 AppDialog
6. `python -m unittest discover -s tests` 与 `python tests/smoke_gui.py` 全部通过

## 5. 风险与回退

- 边缘拉伸 eventFilter 若拦截过宽会影响子控件正常交互 → 只在非拉伸模式下放行,出问题可整体回退 main_window.py 单文件
- QSplitter 嵌在滚动区内的高度策略若抖动 → 回退为固定比例 + 单卡片内滚动
